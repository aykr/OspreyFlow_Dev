"""*Admin › Models* (`06_DECISIONS.md` ADR-135 Amendment 2, ADR-112 Amendment 7): the engines, each
job's default engine, each key's record and state, the connection test and the history.

**No model here has a field that can hold a key** except `KeyInput`, which the Conduit reads as a
`SecretStr` and never returns. A key's record is when and by whom it was set; its state is "set",
"none" or "lost" (the gateway no longer holds it, ADR-135 Amendment 2 decision 9).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from schemas.deployment import ModelProviderConfig

KeyState = Literal["set", "none", "lost"]
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
]
ConnectionOutcome = Literal[
    "ok",
    "not_routed",
    "gateway_token",
    "key_refused",
    "model_not_offered",
    "cooling_down",
    "rate_limited",
    "unreachable",
]


class AdminEngine(BaseModel):
    """One hosted engine as *Admin › Models* shows it: its settings, and its key's state and record
    — never the key."""

    provider: ModelProviderConfig
    key_state: KeyState
    key_set_at: datetime | None = None
    key_set_by: str | None = None
    #: The roles this engine is the default for.
    default_for: list[str] = Field(default_factory=list)


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
)
