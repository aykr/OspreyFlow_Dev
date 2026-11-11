"""*Admin › Models* (`06_DECISIONS.md` ADR-135 Amendments 2 and 3, ADR-112 Amendment 7): the
engines, each job's default engine, each key's record and state, the connection test, the history,
each engine's limits and the usage the gateway recorded.

**No model here has a field that can hold a key** except `KeyInput`, which the Conduit reads as a
`SecretStr` and never returns. A key's record is when and by whom it was set; its state is "set",
"none" or "lost" (the gateway no longer holds it, ADR-135 Amendment 2 decision 9), or "iam_role" for
an engine that signs in by the gateway's own IAM role and keeps no key (ADR-135 Amendment 4).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from schemas.deployment import EngineKind, ModelProviderConfig

#: `iam_role`: the engine signs in by the gateway's own IAM role (ADR-135 Amendment 4), so it has no
#: key to set, lose or remove.
KeyState = Literal["set", "none", "lost", "iam_role"]
ModelAdminAction = Literal[
    "engine_added",
    "engine_edited",
    "engine_removed",
    "default_changed",
    "key_set",
    "key_rotated",
    "key_removed",
    "key_moved",
    "connection_tested",
    "limits_changed",
]
ConnectionOutcome = Literal[
    "ok",
    "not_routed",
    "gateway_token",
    "key_refused",
    "model_not_offered",
    # ADR-135 Amendment 7 decision 5: Bedrock's model access not granted, its sign-in expired, and a
    # client gateway's 4xx in a shape that is not OpenAI's.
    "model_not_enabled",
    "sign_in_expired",
    "request_refused",
    "cooling_down",
    "rate_limited",
    "unreachable",
]


BudgetPeriod = Literal["day", "month"]
#: What every profile but `cloud-platform` offers (ADR-135 Amendment 7 decision 1).
_PROVIDER_ONLY: tuple[EngineKind, ...] = ("provider",)


class EngineLimits(BaseModel):
    """An engine's limits (ADR-135 Amendment 3), applied by the model gateway to every call the
    Conduit sends that engine. Each is optional; none set is no limit. A budget is in tokens (prompt
    and completion together) per day or per calendar month, UTC; the call that crosses it is
    answered and the next one refused."""

    model_config = ConfigDict(extra="forbid")

    requests_per_minute: int | None = Field(default=None, ge=1, le=1_000_000)
    tokens_per_minute: int | None = Field(default=None, ge=1, le=1_000_000_000)
    budget_tokens: int | None = Field(default=None, ge=1, le=1_000_000_000_000)
    budget_period: BudgetPeriod | None = None

    @model_validator(mode="after")
    def _a_budget_has_its_period(self) -> EngineLimits:
        if (self.budget_tokens is None) != (self.budget_period is None):
            raise ValueError("a budget needs both its tokens and its period (day or month)")
        return self


class AdminEngine(BaseModel):
    """One hosted engine as *Admin › Models* shows it: its settings, its limits, and its key's state
    and record — never the key."""

    provider: ModelProviderConfig
    key_state: KeyState
    key_set_at: datetime | None = None
    key_set_by: str | None = None
    #: The roles this engine is the default for.
    default_for: list[str] = Field(default_factory=list)
    limits: EngineLimits = Field(default_factory=EngineLimits)
    #: On `cloud-platform`, an engine the render made no way out (or, for Bedrock, no role) for,
    #: as a restored models file can hold: "not made by the render: <words>". Such an engine is
    #: never written into the gateway nor offered to analysts (ADR-135 Amendment 8).
    not_made: str | None = None


class ModelsAdminView(BaseModel):
    """`GET /v1/admin/models`."""

    engines: list[AdminEngine]
    #: Each role's default engine (`local`, or an engine's name); a role not here runs locally.
    defaults: dict[str, str]
    #: The deployment's own model for each role, from the pinned lists (ADR-095), read-only here.
    local_models: dict[str, str | None]
    #: `osprey.yaml`'s declarations, read-only here: the installer's
    #: (ADR-135 Amendment 2 decision 1).
    local_only: bool
    sendable_handling_codes: list[str]
    #: Where the settings come from: `osprey.yaml` until the first change here, then the
    #: models file.
    source: Literal["osprey.yaml", "models file"]
    #: The kinds of engine this deployment's profile takes (ADR-135 Amendment 7 decision 1): a
    #: provider alone, or on `cloud-platform` also the client's gateway and Bedrock in London.
    engine_kinds: list[EngineKind] = Field(default_factory=lambda: list(_PROVIDER_ONLY))


class EngineInput(BaseModel):
    """An engine added or edited. Validated as `ModelProviderConfig` is."""

    model_config = ConfigDict(extra="forbid")

    provider: ModelProviderConfig


class DefaultsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: dict[str, str]


class KeyInput(BaseModel):
    """`PUT /v1/admin/models/engines/{name}/key`. Write-only: never echoed, logged or stored by the
    Conduit."""

    model_config = ConfigDict(extra="forbid")

    key: SecretStr = Field(min_length=1, max_length=4096)


class ConnectionTestResult(BaseModel):
    engine: str
    outcome: ConnectionOutcome
    ok: bool
    #: Fixed words for the outcome, never the gateway's or the provider's.
    words: str


class LimitsInput(BaseModel):
    """`PUT /v1/admin/models/engines/{name}/limits`."""

    model_config = ConfigDict(extra="forbid")

    limits: EngineLimits


class UsageFigures(BaseModel):
    """Counts only (ADR-135 Amendment 3 decision 3): never a prompt, an answer, a key, a person or
    a source-system identifier. `calls` counts every call the gateway recorded, refused ones
    included; tokens are those the engine reported."""

    calls: int = 0
    succeeded: int = 0
    failed: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens: int = 0


class UsageRow(BaseModel):
    """One engine and one job over the period."""

    engine: str
    engine_label: str
    job: str
    figures: UsageFigures


class ModelUsageView(BaseModel):
    """`GET /v1/admin/models/usage`: the gateway's own records over the period, by engine and job.
    The period is whole days, UTC, both ends included."""

    start: date
    end: date
    rows: list[UsageRow]
    by_engine: dict[str, UsageFigures]
    by_job: dict[str, UsageFigures]
    total: UsageFigures


class ModelAdminEntry(BaseModel):
    """One row of the engines' history. Never a key, a fragment, a hash or a length."""

    at: datetime
    by: str
    action: ModelAdminAction
    engine: str | None
    #: For an edit, each changed field's old and new value (none of them secret).
    changes: dict[str, dict[str, object]] = Field(default_factory=dict)
    outcome: str


class ModelAdminHistory(BaseModel):
    entries: list[ModelAdminEntry]


ALL_MODELS: tuple[type[BaseModel], ...] = (
    AdminEngine,
    ModelsAdminView,
    EngineInput,
    DefaultsInput,
    KeyInput,
    ConnectionTestResult,
    ModelAdminEntry,
    ModelAdminHistory,
    EngineLimits,
    LimitsInput,
    UsageFigures,
    UsageRow,
    ModelUsageView,
)
