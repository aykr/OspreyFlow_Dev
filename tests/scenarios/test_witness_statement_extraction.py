"""Extraction against a real paragraph of prose, not a one-line toy string —
This stage's own scoping named this fixture explicitly: a short
synthetic witness statement as the running smoke-test document for schema-constrained text
extraction, to be folded into Stage 3's golden set as its first hand-labelled example.

This is a scenario smoke test, not a `ModelPort` conformance case: it exercises one adapter
(`adapters/model_litellm`) against one fixture document, rather than proving the port's contract
generically the way `tests/conformance/model_port/test_suite.py` does. Needs a live LiteLLM/Ollama
(`make dev-up`) — excluded from plain `make test` the same way that suite is.

Asserts shape only — a non-empty list of non-empty strings — never that a specific named person
(Callum PRICE, the subject of the statement's own complaint) was actually found. Checked directly,
not assumed: run three times against the live pinned model, it named Callum PRICE in two runs and
omitted him in the third, extracting only the reporting witness and the location instead — genuine
run-to-run recall variance from a 0.5B-parameter model, not a flake in this test. That is exactly
what `06_DECISIONS.md` ADR-020 already warns extraction *quality* assertions cannot survive on this
pin, and precision/recall against a document like this one is what Stage 3's golden set exists to
measure properly, with a real sample size and a stated threshold — not a single boolean check here.
This test proves the mechanism runs end to end against a real paragraph of prose, nothing more.
"""

from __future__ import annotations

from tests.scenarios.fixtures.witness_statement import (
    WITNESS_STATEMENT_SCHEMA,
    WITNESS_STATEMENT_TEXT,
)

from adapters.model_litellm import CONFORMANCE_MODEL
from adapters.model_litellm.testing import model_litellm_adapter
from schemas.model import ExtractionRequest


async def test_extract_returns_nonempty_persons_from_the_witness_statement() -> None:
    request = ExtractionRequest(
        document_id="witness-statement-1",
        text=WITNESS_STATEMENT_TEXT,
        json_schema=WITNESS_STATEMENT_SCHEMA,
        model=CONFORMANCE_MODEL,
    )
    async with model_litellm_adapter() as adapter:
        result = await adapter.extract(request)

    persons = result.data["persons_mentioned"]
    assert isinstance(persons, list)
    assert persons  # extracted *something* from a real paragraph, not an empty result
    assert all(isinstance(p, str) and p for p in persons)
