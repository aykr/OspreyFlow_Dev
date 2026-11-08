"""`adapters.model_litellm.usage` (`06_DECISIONS.md` ADR-135 Amendment 3): which 429s are an
engine's limit, and which tags are the Conduit's own.

- a limit is only the gateway's own refusal of a key's limit, by its type **and** its words: a
  cooldown's 429 and a provider's own 429 passed through are not an engine's limit, and must not be
  told to a person as one set in *Admin › Models*;
- an engine of any name the schema accepts is read back from its tag, so none is left out of the
  figures; anything not of the Conduit's shape is never read.
"""

from __future__ import annotations

import httpx
import pytest

from adapters.model_litellm.usage import Call, limit_refusal, parse_tag, usage_tag


def _429(kind: str, message: str) -> httpx.Response:
    return httpx.Response(429, json={"error": {"message": message, "type": kind, "code": "429"}})


def test_the_measured_rate_refusals_are_limits_with_their_kind_and_reset() -> None:
    requests = limit_refusal(
        _429(
            "throttling_error",
            (
                "Rate limit exceeded for api_key: 9aed96. Limit type: requests. Current limit: 2, "
                "Remaining: 0. Limit resets at: 2026-11-08 17:43:04 UTC"
            ),
        )
    )
    tokens = limit_refusal(
        _429(
            "throttling_error",
            (
                "Rate limit exceeded for model_per_key: 34c6:prov/costly. Limit type: tokens. "
                "Current limit: 30, Remaining: 0. Limit resets at: 2026-11-08 17:43:17 UTC"
            ),
        )
    )
    assert requests is not None and requests.kind == "requests"
    assert requests.resets_at is not None and requests.resets_at.minute == 43
    assert tokens is not None and tokens.kind == "tokens"


def test_the_measured_budget_refusal_is_a_limit() -> None:
    hit = limit_refusal(
        _429(
            "budget_exceeded",
            (
                "Budget has been exceeded! Key=osprey (sk-...0001) Current cost: 66.0, "
                "Max budget: 50.0"
            ),
        )
    )
    assert hit is not None and hit.kind == "budget"


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        # The cooldown after a failure (measured).
        (
            "internal_server_error",
            "No deployments available for selected model, Try again in 5 "
            "seconds. Passed model=gemini/x. pre-call-checks=False, cooldown_list=['osprey-x']",
        ),
        # A provider's own 429 through the gateway: not measured, so whatever its type, it is not
        # an engine's limit unless the gateway says so in its own words.
        (
            "throttling_error",
            "litellm.RateLimitError: RateLimitError: OpenAIException - Rate limit "
            "reached for gpt-4o-mini on tokens per min (TPM): Limit 200000, Used 199990",
        ),
        ("rate_limit_error", "Rate limit reached for requests"),
        ("budget_exceeded", "a provider's quota is used up"),
    ],
    ids=["cooldown", "provider-throttling", "provider-rate-limit", "budget-type-other-words"],
)
def test_any_other_429_is_not_an_engine_s_limit(kind: str, message: str) -> None:
    assert limit_refusal(_429(kind, message)) is None


def test_a_non_429_is_never_a_limit() -> None:
    assert (
        limit_refusal(
            httpx.Response(
                500,
                json={"error": {"type": "budget_exceeded", "message": "Budget has been exceeded!"}},
            )
        )
        is None
    )


@pytest.mark.parametrize("engine", ["openai", "azure_openai_uk_south_production_two", "local"])
def test_an_engine_of_any_name_the_schema_takes_comes_back_from_its_tag(engine: str) -> None:
    assert parse_tag(usage_tag(engine, "extraction")) == Call(engine, "extraction")


@pytest.mark.parametrize(
    "tag",
    [
        "User-Agent: python-httpx/0.28",
        "osprey:",
        "osprey:openai",
        "osprey:../x",
        "osprey:Open/x",
        "osprey:openai/extraction/more",
        "job:extraction",
    ],
)
def test_a_tag_not_of_the_conduit_s_shape_is_never_read(tag: str) -> None:
    assert parse_tag(tag) is None
