"""*Admin › Models*' provider list (the owner's prompt of 15 November 2026, Part 1; ADR-135
Amendment 14 point 1; PREBUILD_FINDINGS.md §3.1): the form chooses a provider from a list, and
the provider brings its address, its LiteLLM prefix, whether it has a key, a current model as
its example, the hosts a check calls and only the jobs it can do.

What a mistake would do, and the case that catches it (rule 12):
- a job offered that the provider cannot do (Anthropic's or Bedrock's transcription):
  `test_each_provider_offers_only_the_jobs_it_can_do`;
- Bedrock offered where it cannot run, or with a key or an address:
  `test_bedrock_is_offered_on_the_cloud_platform_alone_with_no_key_and_no_address`;
- a model id sent to the gateway without the provider's prefix, or with it twice:
  `test_the_prefix_is_the_form_s_business`;
- a provider the form lists that `ModelProviderConfig` refuses:
  `test_each_entry_makes_a_valid_engine`;
- an example that is deprecated, or that Bedrock's London rule refuses:
  `test_no_example_is_a_deprecated_model`, `test_bedrock_s_example_is_one_its_own_rule_takes`.
"""

from __future__ import annotations

import pytest
from services.api import model_catalogue as cat

from schemas.deployment import ModelProviderConfig, engine_refusal

CLOUD = "cloud-platform"


def test_the_list_is_the_owner_s_in_the_owner_s_order() -> None:
    assert [p.id for p in cat.providers(CLOUD)] == [
        "gemini", "openai", "anthropic", "azure", "bedrock", "gateway",
    ]  # fmt: skip
    assert [p.label for p in cat.providers(CLOUD)] == [
        "Google Gemini", "OpenAI", "Anthropic", "Azure OpenAI", "Amazon Bedrock",
        "Another provider or your own gateway",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("provider", "jobs"),
    [
        ("gemini", ("extraction", "vision", "transcription")),
        ("openai", ("extraction", "vision", "transcription")),
        ("anthropic", ("extraction", "vision")),
        ("azure", ("extraction", "vision", "transcription")),
        ("bedrock", ("extraction", "vision")),
        ("gateway", ("extraction", "vision", "transcription")),
    ],
)
def test_each_provider_offers_only_the_jobs_it_can_do(provider: str, jobs: tuple[str, ...]) -> None:
    assert cat.provider(provider, CLOUD).jobs == jobs


def test_bedrock_is_offered_on_the_cloud_platform_alone_with_no_key_and_no_address() -> None:
    bedrock = cat.provider("bedrock", CLOUD)
    assert not bedrock.key and bedrock.address is None and not bedrock.address_asked
    assert "London" in bedrock.note and "role" in bedrock.note
    for profile in ("small", "local-lite", "cluster"):
        assert "bedrock" not in [p.id for p in cat.providers(profile)]
        with pytest.raises(cat.NotOffered):
            cat.provider("bedrock", profile)


def test_the_addresses_are_the_providers_own_and_asked_where_there_is_none() -> None:
    assert cat.provider("gemini", CLOUD).address == "https://generativelanguage.googleapis.com"
    assert cat.provider("openai", CLOUD).address == "https://api.openai.com"
    assert cat.provider("anthropic", CLOUD).address == "https://api.anthropic.com"
    for asked in ("azure", "gateway"):
        entry = cat.provider(asked, CLOUD)
        assert entry.address is None and entry.address_asked


@pytest.mark.parametrize(
    ("provider", "model", "routed"),
    [
        ("gemini", "gemini-3.8-flash", "gemini/gemini-3.8-flash"),
        ("gemini", "gemini/gemini-3.8-flash", "gemini/gemini-3.8-flash"),  # a discovered id
        ("anthropic", "claude-sonnet-5-5", "anthropic/claude-sonnet-5-5"),
        ("azure", "my-gpt-deployment", "azure/my-gpt-deployment"),
        ("bedrock", "anthropic.claude-sonnet-5-5-v1:0", "bedrock/anthropic.claude-sonnet-5-5-v1:0"),
        ("gateway", "llama-4", "openai/llama-4"),
    ],
)
def test_the_prefix_is_the_form_s_business(provider: str, model: str, routed: str) -> None:
    assert cat.routed(provider, model) == routed
    assert cat.bare(provider, routed) == model.split("/", 1)[-1] if "/" in model else model


@pytest.mark.parametrize(
    ("provider", "example"),
    [
        ("gemini", "gemini-3.8-flash"),  # never the deprecated gemini-2.5-flash
        ("openai", "gpt-6.1-sol"),
        ("anthropic", "claude-sonnet-5-5"),
        ("bedrock", "amazon.nova-pro-v1:0"),  # served in London; Claude is not, in the Region
        ("azure", None),  # the deployment's name is the client's own
        ("gateway", None),
    ],
)
def test_each_provider_names_a_current_model_as_its_example(
    provider: str, example: str | None
) -> None:
    assert cat.provider(provider, CLOUD).example == example


def test_no_example_is_a_deprecated_model() -> None:
    assert "gemini-2.5-flash" not in [p.example for p in cat.providers(CLOUD)]


def test_bedrock_s_example_is_one_its_own_rule_takes() -> None:
    """ADR-135 Amendment 7 decision 2: a Bedrock model is named by its own id, never a profile's."""
    entry = cat.provider("bedrock", CLOUD)
    assert entry.example is not None
    engine = ModelProviderConfig.model_validate(
        {
            **cat.engine_fields(entry, label=entry.label, address=None),
            "roles": {"extraction": entry.example},
        }
    )
    assert engine_refusal(engine, CLOUD) is None


@pytest.mark.parametrize(
    "provider", ["gemini", "openai", "anthropic", "azure", "bedrock", "gateway"]
)
def test_each_entry_makes_a_valid_engine(provider: str) -> None:
    entry = cat.provider(provider, CLOUD)
    fields = cat.engine_fields(entry, label=entry.label, address="https://example.openai.azure.com")
    model = "anthropic.a-model-v1:0" if provider == "bedrock" else "a-model"
    engine = ModelProviderConfig.model_validate({**fields, "roles": {entry.jobs[0]: model}})
    assert engine_refusal(engine, CLOUD) is None, engine_refusal(engine, CLOUD)
    assert engine.route(model) == cat.routed(provider, model)


@pytest.mark.parametrize("profile", ["small", "local-lite", "cluster", CLOUD])
def test_another_provider_or_your_own_gateway_is_offered_on_every_profile(profile: str) -> None:
    """The owner's ruling of 15 November 2026 (ADR-135 Amendment 14, changing Amendment 7
    decision 1): the client's own gateway on every profile, a Small's included."""
    assert "gateway" in [p.id for p in cat.providers(profile)]


@pytest.mark.parametrize("profile", ["small", "local-lite", "cluster"])
def test_off_the_cloud_platform_a_gateway_engine_is_taken_and_bedrock_is_not(profile: str) -> None:
    gateway = ModelProviderConfig.model_validate({
        "name": "gateway", "kind": "gateway", "api_base": "https://ai.example.gov.uk/v1",
        "roles": {"extraction": "llama-4"},
    })  # fmt: skip
    assert engine_refusal(gateway, profile) is None, engine_refusal(gateway, profile)
    keyed_address = gateway.model_copy(
        update={"api_base": "https://ai.example.gov.uk/v1?api-key=x"}
    )
    assert engine_refusal(keyed_address, profile) is not None, "an address is an address alone"
    no_address = gateway.model_copy(update={"api_base": None})
    assert engine_refusal(no_address, profile) is not None
    bedrock = ModelProviderConfig.model_validate(
        {"name": "bedrock", "kind": "bedrock", "roles": {"extraction": "amazon.nova-pro-v1:0"}}
    )
    assert engine_refusal(bedrock, profile) is not None, "Bedrock stays the cloud platform's"
