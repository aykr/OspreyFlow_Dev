"""Laurium's service refuses, at start, any setting that would send a model call anywhere but the
deployment's gateway (`06_DECISIONS.md` ADR-135 Amendment 6 decision 4).

Each plant is the shape the service really reads at its own call site: the process environment as a
mapping of strings, read whole by `Settings.from_env` before the app serves anything
(`services/laurium/app.py`). The built image's own refusal, the same check in the real container, is
`tests/conformance/model_port/test_laurium_service.py`.
"""

from __future__ import annotations

import pytest

from services.laurium.settings import GATEWAY_HOST, RefusedSetting, Settings

GOOD = {"OSPREY_LAURIUM_GATEWAY_URL": "http://litellm:4000", "PATH": "/usr/bin", "HOME": "/srv"}


def _refusal(env: dict[str, str]) -> str:
    with pytest.raises(RefusedSetting) as caught:
        Settings.from_env(env)
    return str(caught.value)


def test_the_gateway_alone_is_accepted() -> None:
    settings = Settings.from_env(GOOD)
    assert settings.gateway_url == "http://litellm:4000"
    assert GATEWAY_HOST == "litellm"


def test_the_gateway_with_its_v1_path_is_accepted() -> None:
    assert Settings.from_env({**GOOD, "OSPREY_LAURIUM_GATEWAY_URL": "http://litellm:4000/v1"})


def test_no_gateway_url_is_refused() -> None:
    assert "OSPREY_LAURIUM_GATEWAY_URL" in _refusal({"PATH": "/usr/bin"})


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "http://ollama:11434",
        "http://litellm.attacker.example:4000",
        "http://evil.example/litellm:4000",
        "http://user:pass@evil.example:4000",
        "http://litellm@evil.example:4000",
        "http://127.0.0.1:4000",
        "ftp://litellm:4000",
        "litellm:4000",
        # The gateway's name, but with a credential in the URL, a path elsewhere, or no port.
        "http://user:secret@litellm:4000",
        "http://litellm:4000/elsewhere",
        "http://litellm:4000/v1?to=elsewhere.example",
        "http://litellm",
    ],
)
def test_a_gateway_url_naming_any_other_host_is_refused(url: str) -> None:
    words = _refusal({**GOOD, "OSPREY_LAURIUM_GATEWAY_URL": url})
    assert "gateway" in words


@pytest.mark.parametrize(
    "name",
    [
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
        "OPENAI_PROXY",
        "OLLAMA_HOST",
        "OLLAMA_BASE_URL",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_URL",
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_BEDROCK_RUNTIME",
        "LANGSMITH_ENDPOINT",
        "LANGCHAIN_ENDPOINT",
        "HTTP_PROXY",
        "https_proxy",
        "ALL_PROXY",
    ],
)
def test_a_library_setting_naming_a_host_is_refused(name: str) -> None:
    words = _refusal({**GOOD, name: "https://elsewhere.example"})
    assert name in words


@pytest.mark.parametrize(
    "name", ["LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING", "LANGSMITH_TRACING_V2"]
)
def test_langsmith_tracing_on_is_refused(name: str) -> None:
    assert name in _refusal({**GOOD, name: "true"})


@pytest.mark.parametrize("value", ["false", "0", ""])
def test_langsmith_tracing_off_is_accepted(value: str) -> None:
    assert Settings.from_env({**GOOD, "LANGSMITH_TRACING": value})


@pytest.mark.parametrize(
    "env",
    [
        # Two spellings of one name: the libraries read either (urllib prefers the lower case), so
        # one set to anything is refused whatever the other says.
        {"OPENAI_PROXY": "http://evil.example:3128", "openai_proxy": ""},
        {"https_proxy": "http://evil.example:3128", "HTTPS_PROXY": ""},
        {"LANGSMITH_TRACING": "true", "langsmith_tracing": "false"},
    ],
)
def test_one_spelling_set_is_refused_whatever_the_other_says(env: dict[str, str]) -> None:
    _refusal({**GOOD, **env})


@pytest.mark.parametrize("name", ["LOCALDOMAIN", "RES_OPTIONS", "HOSTALIASES"])
def test_a_setting_that_changes_what_litellm_resolves_to_is_refused(name: str) -> None:
    """The gateway is the single-label name `litellm`; these make the resolver look it up
    elsewhere."""
    assert name in _refusal({**GOOD, name: "evil.example"})


@pytest.mark.parametrize("name", ["OPENAI_LOG", "LANGCHAIN_VERBOSE", "LANGCHAIN_DEBUG"])
def test_a_setting_that_logs_what_is_sent_is_refused(name: str) -> None:
    """The OpenAI client's and LangChain's debug logs write each request, a document's text
    with it; nothing of a document is logged (app.py)."""
    assert name in _refusal({**GOOD, name: "debug"})


def test_an_unknown_laurium_setting_is_refused() -> None:
    """A setting the service does not read is refused rather than ignored: a mistyped or invented
    `OSPREY_LAURIUM_LLM_PLATFORM=bedrock` must not look as if it took effect."""
    assert "OSPREY_LAURIUM_LLM_PLATFORM" in _refusal(
        {**GOOD, "OSPREY_LAURIUM_LLM_PLATFORM": "bedrock"}
    )


def test_every_refusal_is_named_at_once() -> None:
    words = _refusal(
        {**GOOD, "OPENAI_BASE_URL": "https://a.example", "LANGSMITH_TRACING": "true"}
    )
    assert "OPENAI_BASE_URL" in words and "LANGSMITH_TRACING" in words


def test_the_refusal_never_repeats_a_value() -> None:
    """A proxy setting can carry credentials (`http://user:secret@proxy`); the words name the
    setting, never its value."""
    words = _refusal({**GOOD, "HTTPS_PROXY": "http://user:s3cret-value@proxy.example:3128"})
    assert "s3cret-value" not in words


def test_a_timeout_is_read() -> None:
    settings = Settings.from_env({**GOOD, "OSPREY_LAURIUM_TIMEOUT_SECONDS": "120"})
    assert settings.timeout_seconds == 120.0


@pytest.mark.parametrize("value", ["soon", "0", "-5"])
def test_a_timeout_that_is_not_a_positive_number_is_refused(value: str) -> None:
    assert "OSPREY_LAURIUM_TIMEOUT_SECONDS" in _refusal(
        {**GOOD, "OSPREY_LAURIUM_TIMEOUT_SECONDS": value}
    )
