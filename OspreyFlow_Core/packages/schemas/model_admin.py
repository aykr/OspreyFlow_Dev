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
    # ADR-135 Amendment 14: the check before Add, and a passed check cancelled or left 15 minutes.
    "engine_checked",
    "engine_check_cancelled",
    "engine_check_expired",
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


class CatalogueEntry(BaseModel):
    """One provider of *Admin › Models*' list (ADR-135 Amendment 14 point 1), as the form shows it:
    its own address or that it asks one, whether it signs in by a key, its jobs alone, a current
    model as the example beside the typed name, and LiteLLM's prefix, which the form takes off a
    name typed with it. The hosts a check calls stay in the Conduit."""

    id: str
    label: str
    kind: EngineKind
    address: str | None
    address_asked: bool
    key: bool
    example: str | None
    jobs: list[str]
    prefix: str
    note: str = ""


class HeldCheck(BaseModel):
    """A passed check waiting for **Add** (ADR-135 Amendment 14 point 2), shown in Admin as being
    checked so it can be cancelled; never an engine, never offered to analysts."""

    id: str
    engine: str
    label: str
    by: str
    at: datetime
    expires_at: datetime


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
    #: ADR-135 Amendment 5 decision 2 and Amendment 9: the extraction engine the deployment was
    #: rendered with, chosen at set-up (`osprey.yaml`), read-only here.
    extraction_engine: Literal["deep_read", "laurium"] = "deep_read"
    #: ADR-135 Amendment 14: the providers this profile offers the add form, in the owner's order.
    providers: list[CatalogueEntry] = Field(default_factory=list)
    #: ADR-135 Amendment 14: the passed checks not yet added, cancelled or 15 minutes old.
    checks: list[HeldCheck] = Field(default_factory=list)


class EngineInput(BaseModel):
    """`PUT /v1/admin/models/engines/{name}`: an engine edited, validated as `ModelProviderConfig`
    is, with its key where the address changed or the key is changed with it; a changed model,
    address or key is checked before it is saved (ADR-135 Amendment 14, the owner's ruling 19).
    Read by hand, so a refusal never echoes the key. An engine is added only from a check."""

    model_config = ConfigDict(extra="forbid")

    provider: ModelProviderConfig
    key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)


class EngineCheckInput(BaseModel):
    """`POST /v1/admin/models/checks` (ADR-135 Amendment 14): an engine not yet added, with its key
    where it has one, proved before **Add**. Read by hand, as `KeyInput` is, so a refusal never
    echoes the key."""

    model_config = ConfigDict(extra="forbid")

    provider: ModelProviderConfig
    key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)


class ModelCheck(BaseModel):
    """One typed model's answer to the check's one call, in fixed words, by the jobs it was typed for:
    never the typed name, which may be a key pasted in the wrong field (the owner's ruling 22)."""

    roles: list[str]
    outcome: ConnectionOutcome
    ok: bool
    words: str


class EngineCheckResult(BaseModel):
    """The check's answer: `check` names a passed check for **Add**, `None` when anything was
    refused (and then nothing of it is kept)."""

    engine: str
    ok: bool
    check: str | None
    models: list[ModelCheck]
    #: Fixed words for the whole: what to do next, never the gateway's or the provider's.
    words: str


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
    EngineCheckInput,
    EngineCheckResult,
    ModelCheck,
    CatalogueEntry,
    HeldCheck,
)
