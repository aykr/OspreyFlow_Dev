"""Typed `ModelPort` failures — never a bare `Exception`, matching the rest of the codebase's
discipline (`ArcadeDBError`, `StaleRecipeError`, `UnsupportedProjectionError`)."""

from __future__ import annotations

from datetime import datetime


class ModelPortError(Exception):
    """Base for every error `adapters/model_litellm` raises."""


class InvalidExtractionSchemaError(ModelPortError):
    """The `response_schema` passed to `extract()` is not a schema the backend can constrain
    decoding against — surfaced as its own type rather than a generic HTTP error so a caller can
    tell "your schema is malformed" apart from "the model/proxy is unavailable"
    (`ExtractionFailedError`) without parsing prose."""


class ExtractionFailedError(ModelPortError):
    """The model's output did not validate against `response_schema` after every retry, or the
    proxy call itself failed for a reason that is not a schema problem (timeout, transport error,
    non-2xx unrelated to the schema)."""


class ModelUnavailableError(ExtractionFailedError):
    """The proxy cannot serve the model named: not routed, or not (yet) pulled — the proxy answers
    `404` for both. Seen while a deployment's chosen extraction model was still downloading
    (ADR-095). A subclass of `ExtractionFailedError`, so every caller that already handles a
    failed extraction still does; the Conduit tells an analyst which it was."""


class EmbeddingFailedError(ModelPortError):
    """The proxy returned a different number of embedding vectors than inputs given to `embed()`
    — a shape violation `embed()` has no schema to catch the way `extract()` does, so this is the
    one thing worth checking before trusting the result."""


class TranscriptionFailedError(ModelPortError):
    """The `/audio/transcriptions` call itself failed (timeout, transport error, non-2xx) —
    `transcribe()` has no schema and no retry loop the way `extract()` does, so any proxy failure
    surfaces here directly."""


class ModelLimitReached(ExtractionFailedError):
    """The model gateway refused a call because an engine's limit set in *Admin › Models* was
    reached (ADR-135 Amendment 3): its requests or tokens a minute, or its token budget. Built from
    the refusal's type, kind and reset time only, never its words, which name the gateway key's
    hash or part of it. A subclass of `ExtractionFailedError`, so every caller that already handles
    a failed model call still does; the Conduit says it to a person in `words`."""

    def __init__(
        self,
        kind: str,
        *,
        resets_at: datetime | None = None,
        engine_label: str | None = None,
        budget_period: str | None = None,
    ) -> None:
        self.kind = kind
        self.resets_at = resets_at
        self.engine_label = engine_label
        self.budget_period = budget_period
        super().__init__(self.words)

    @property
    def words(self) -> str:
        engine = self.engine_label or "This engine"
        if self.kind == "budget":
            reached, later = {
                "day": ("has used its token budget for today", "It can be used again from "
                        "midnight UTC"),
                "month": ("has used its token budget for this month", "It can be used again from "
                          "the first of next month"),
            }.get(self.budget_period or "", ("has used its token budget", "It can be used again "
                                             "when the budget resets"))  # fmt: skip
        else:
            per = "requests" if self.kind == "requests" else "tokens"
            reached = f"has reached its limit of {per} a minute"
            later = (
                f"Try again after {self.resets_at:%H:%M} UTC"
                if self.resets_at
                else "Try again in a minute"
            )
        return (
            f"{engine} {reached} on this deployment, set in Admin › Models. {later}, or ask "
            "someone who manages models. Nothing was sent to it."
        )

    def for_engine(self, label: str, budget_period: str | None = None) -> ModelLimitReached:
        return ModelLimitReached(
            self.kind, resets_at=self.resets_at, engine_label=label, budget_period=budget_period
        )


class ModelEngineRefused(ExtractionFailedError):
    """The engine behind the gateway refused or failed the call, or gave no answer in time
    (ADR-135 Amendment 13). Each kind is a refusal measured through the pinned gateway
    (`usage.provider_refusal`):

    - `busy`: the provider's own rate limit or quota, not a limit set in *Admin › Models*;
    - `key`: the provider refused the engine's key, or that key may not use the model;
    - `unavailable`: the provider failed after the gateway's own retries, or the gateway is
      resting the engine after a failure (its cooldown);
    - `timed_out`: no answer within the deployment's bound for this engine.

    Built from the kind alone, never the refusal's words, which can carry part of a key. A
    subclass of `ExtractionFailedError`, so every caller that already handles a failed model call
    still does; the Conduit says it to a person in `words`."""

    def __init__(
        self, kind: str, *, engine_label: str | None = None, timeout_seconds: float | None = None
    ) -> None:
        self.kind = kind
        self.engine_label = engine_label
        self.timeout_seconds = timeout_seconds
        super().__init__(self.words)

    @property
    def words(self) -> str:
        engine = self.engine_label or "The model"
        if self.kind == "busy":
            said = (
                f"{engine} is refusing more requests just now: its provider's own rate limit or "
                "quota was reached, not a limit set on this deployment. Try again in a few "
                "minutes; if it goes on, ask someone who manages models to check the provider's "
                "quota."
            )
        elif self.kind == "key":
            said = (
                f"{engine}'s provider refused this deployment's key for it, or that key may not "
                "use this model. Ask someone who manages models to check the engine's key in "
                "Admin › Models."
            )
        elif self.kind == "timed_out":
            bound = f" ({self.timeout_seconds:g} seconds)" if self.timeout_seconds else ""
            said = (
                f"{engine} did not answer within the time this deployment allows{bound}, so the "
                "request was stopped. Try again, or with less text."
            )
        else:
            said = f"{engine}'s provider could not answer just now. Try again in a minute."
        return f"{said} Nothing was recorded."

    def for_engine(self, label: str) -> ModelEngineRefused:
        return ModelEngineRefused(
            self.kind, engine_label=label, timeout_seconds=self.timeout_seconds
        )


class UsageUnavailableError(ModelPortError):
    """The gateway's usage records could not be read, in fixed words (never the gateway's)."""
