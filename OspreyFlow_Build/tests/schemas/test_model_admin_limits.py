"""`schemas.model_admin`'s limits and usage shapes (`06_DECISIONS.md` ADR-135 Amendment 3).

- an engine's budget is refused without its period, and a period without its budget, so a budget
  can never be half set and silently mean no limit;
- a limit is refused at zero or below, and the shape refuses any other key;
- usage figures hold counts only: no field of the usage view can carry text but the engine's name
  and label and the job's name (rule 7 and decision 3).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.model_admin import EngineLimits, LimitsInput, ModelUsageView, UsageFigures, UsageRow


def test_no_limit_is_the_default() -> None:
    limits = EngineLimits()
    assert limits.model_dump() == {
        "requests_per_minute": None,
        "tokens_per_minute": None,
        "budget_tokens": None,
        "budget_period": None,
    }


@pytest.mark.parametrize(
    "half",
    [{"budget_tokens": 1000}, {"budget_period": "month"}],
    ids=["tokens-without-period", "period-without-tokens"],
)
def test_a_budget_without_its_period_or_tokens_is_refused(half: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="a budget needs both"):
        EngineLimits.model_validate(half)


def test_a_whole_budget_and_rates_are_taken() -> None:
    limits = EngineLimits(
        requests_per_minute=60, tokens_per_minute=100_000, budget_tokens=5_000_000,
        budget_period="day",
    )  # fmt: skip
    assert limits.budget_period == "day" and limits.budget_tokens == 5_000_000


@pytest.mark.parametrize("field", ["requests_per_minute", "tokens_per_minute", "budget_tokens"])
def test_a_limit_of_zero_is_refused(field: str) -> None:
    body: dict[str, object] = {field: 0}
    if field == "budget_tokens":
        body["budget_period"] = "day"
    with pytest.raises(ValidationError):
        EngineLimits.model_validate(body)


def test_the_limits_body_refuses_any_other_key() -> None:
    with pytest.raises(ValidationError):
        LimitsInput.model_validate({"limits": {}, "person": "someone"})
    with pytest.raises(ValidationError):
        LimitsInput.model_validate({"limits": {"budget_dollars": 5}})


def test_usage_carries_counts_and_names_only() -> None:
    assert set(UsageFigures.model_fields) == {
        "calls", "succeeded", "failed", "prompt_tokens", "completion_tokens", "tokens",
    }  # fmt: skip
    assert all(f.annotation is int for f in UsageFigures.model_fields.values())
    assert set(UsageRow.model_fields) == {"engine", "engine_label", "job", "figures"}
    assert set(ModelUsageView.model_fields) == {
        "start", "end", "rows", "by_engine", "by_job", "total",
    }  # fmt: skip
