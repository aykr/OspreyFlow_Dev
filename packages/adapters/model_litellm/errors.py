"""Typed `ModelPort` failures — never a bare `Exception`, matching the rest of the codebase's
discipline (`ArcadeDBError`, `StaleRecipeError`, `UnsupportedProjectionError`)."""

from __future__ import annotations


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


class EmbeddingFailedError(ModelPortError):
    """The proxy returned a different number of embedding vectors than inputs given to `embed()`
    — a shape violation `embed()` has no schema to catch the way `extract()` does, so this is the
    one thing worth checking before trusting the result."""


class TranscriptionFailedError(ModelPortError):
    """The `/audio/transcriptions` call itself failed (timeout, transport error, non-2xx) —
    `transcribe()` has no schema and no retry loop the way `extract()` does, so any proxy failure
    surfaces here directly."""
