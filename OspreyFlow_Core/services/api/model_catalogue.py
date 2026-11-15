"""*Admin › Models*' provider list (the owner's prompt of 15 November 2026, Part 1; ADR-135
Amendment 14 point 1; `process/lanes/admin-forms/PREBUILD_FINDINGS.md` §2 and §3.1). Each entry
is what the form knows of a provider once it is chosen: its label, its own address (or that it
asks for one), whether it signs in by a key, the jobs it can do, a current model named as the
example beside the typed model name, and LiteLLM's prefix, which the form takes off a name typed
with it (the engine's own `route` adds it). Nothing here holds a key.

This is the first slice's list (the owner, 15 November 2026): a model is typed and proved by one
call; listing the models a key may use is not built. The examples were checked against each
provider's own list on 15 November 2026 (Gemini's `gemini-2.5-flash` is deprecated, routed to
`gemini-3.5-flash-lite` from 1 December 2026; on Bedrock in London, Anthropic's current models are
served only through cross-region profiles, which ADR-135 Amendment 7 decision 2 refuses, so the
example is Amazon Nova Pro, served in the Region)."""

from __future__ import annotations

from dataclasses import dataclass

from schemas.deployment import EngineKind, ModelRole, engine_kinds_offered


class NotOffered(LookupError):
    """A provider this deployment's profile does not offer (Bedrock off the cloud platform)."""


@dataclass(frozen=True)
class CatalogueProvider:
    id: str
    label: str
    kind: EngineKind
    #: The provider's own address, shown with "Change" for a gateway; `None` where it is asked or
    #: where the engine takes none (Bedrock).
    address: str | None
    address_asked: bool
    #: Whether it signs in by a key; Bedrock by the gateway's own role.
    key: bool
    #: A current model, shown as the example beside the typed name; `None` where the name is the
    #: client's own (an Azure deployment, a gateway's model).
    example: str | None
    jobs: tuple[ModelRole, ...]
    #: LiteLLM's prefix for this provider's models.
    prefix: str
    note: str = ""


_ALL: tuple[ModelRole, ...] = ("extraction", "vision", "transcription")
_NO_AUDIO: tuple[ModelRole, ...] = ("extraction", "vision")

CATALOGUE: tuple[CatalogueProvider, ...] = (
    CatalogueProvider(
        "gemini", "Google Gemini", "provider", "https://generativelanguage.googleapis.com", False,
        True, "gemini-3.8-flash", _ALL, "gemini",
    ),
    CatalogueProvider(
        "openai", "OpenAI", "provider", "https://api.openai.com", False, True, "gpt-6.1-sol",
        _ALL, "openai",
    ),
    # No audio block in Anthropic's Messages API (PREBUILD_FINDINGS §3.1).
    CatalogueProvider(
        "anthropic", "Anthropic", "provider", "https://api.anthropic.com", False, True,
        "claude-sonnet-5-5", _NO_AUDIO, "anthropic",
    ),
    # Its deployments are named by the administrator: the name is the client's own.
    CatalogueProvider(
        "azure", "Azure OpenAI", "provider", None, True, True, None, _ALL, "azure",
        note="Give your Azure OpenAI resource's address, and each deployment's name.",
    ),
    # ADR-135 Amendment 4 (b): the gateway's own role, London alone; transcription is not Bedrock's.
    CatalogueProvider(
        "bedrock", "Amazon Bedrock", "bedrock", None, False, False, "amazon.nova-pro-v1:0",
        _NO_AUDIO, "bedrock",
        note=(
            "Amazon Bedrock is reached by this deployment's own role, in London only: no key and "
            "no address."
        ),
    ),
    # The client's own OpenAI-compatible gateway (ADR-135 Amendment 4), reached at its address.
    CatalogueProvider(
        "gateway", "Another provider or your own gateway", "gateway", None, True, True, None,
        _ALL, "openai",
        note="Give its address (https://…). Its models are named, and each is checked by one call.",
    ),
)  # fmt: skip


def providers(profile: str) -> list[CatalogueProvider]:
    """The providers this profile offers, in the owner's order: an entry whose kind the profile
    does not offer is left out (ADR-135 Amendment 7 decision 1)."""
    offered = set(engine_kinds_offered(profile))
    return [p for p in CATALOGUE if p.kind in offered]


def provider(id: str, profile: str) -> CatalogueProvider:  # noqa: A002 - the provider's own id
    for entry in providers(profile):
        if entry.id == id:
            return entry
    raise NotOffered(f"{id} is not offered on this deployment")
