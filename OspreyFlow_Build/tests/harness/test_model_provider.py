"""ADR-114 decision 11, Amendment 6 point 4: a client's own model provider, named per deployment.

- **Settings**: `models.provider` names the provider and the roles it takes (each with its model),
  refused in words when it cannot be right — no roles, a bad name, an address that is not HTTPS,
  local_only still on, or the old `hosted_fallback` beside it.
- **The model table**: the rendered `litellm.yaml` routes each provider model through LiteLLM with
  its key read from the environment (`os.environ/…`) — the key itself is in no generated file.
- **The Conduit** is told each role's provider model and the sendable codes; never the key.
- **Apply** writes the key into `deployment.env` only, from `OSPREY_MODEL_PROVIDER_KEY`, and refuses
  in words when a provider is named and no key is given.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness.apply import ApplyFailed, provider_secret_lines
from harness.render import load_config, render, render_litellm_config
from pydantic import ValidationError
from tools.layout import CORE

from schemas.deployment import ModelProviderConfig, ModelsConfig, OspreyConfig
from tests.harness.test_render import FIXTURE_CONFIG, _fake_resolver

KEY = "sk-client-THIS-MUST-NEVER-APPEAR-ANYWHERE"
PROVIDER = ModelProviderConfig(
    name="openai", roles={"extraction": "gpt-4o-mini", "vision": "gpt-4o"}
)


def _config(tmp_path: Path, models: ModelsConfig) -> OspreyConfig:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    return loaded.model_copy(
        update={
            "models": models,
            "components": loaded.components.model_copy(update={"source_path": str(CORE)}),
        }
    )


WITH_PROVIDER = ModelsConfig(local_only=False, provider=PROVIDER, sendable_handling_codes=["P"])


@pytest.mark.parametrize(
    ("fields", "words"),
    [
        ({"local_only": True, "provider": PROVIDER}, "local_only"),
        ({"local_only": False, "provider": PROVIDER, "hosted_fallback": "x"}, "hosted_fallback"),
        ({"local_only": False, "provider": {"name": "openai", "roles": {}}}, "at least one role"),
        ({"local_only": False, "provider": {"name": "Open AI!", "roles": {"extraction": "m"}}},
         "provider name"),
        ({"local_only": False, "provider": {"name": "openai", "roles": {"extraction": "m"},
                                            "api_base": "http://insecure.example"}}, "https"),
        ({"local_only": False, "provider": {"name": "openai", "roles": {"summarise": "m"}}},
         "roles"),
    ],
)
def test_a_provider_that_cannot_be_right_is_refused_in_words(
    fields: dict[str, object], words: str
) -> None:
    with pytest.raises(ValidationError, match=words):
        ModelsConfig.model_validate(fields)


def test_the_model_table_routes_the_provider_with_its_key_read_from_the_environment(
    tmp_path: Path,
) -> None:
    table = yaml.safe_load(render_litellm_config(_config(tmp_path, WITH_PROVIDER)))
    routed = {m["model_name"]: m["litellm_params"] for m in table["model_list"]}
    assert routed["openai/gpt-4o-mini"]["model"] == "openai/gpt-4o-mini"
    assert routed["openai/gpt-4o-mini"]["api_key"] == "os.environ/OSPREY_MODEL_PROVIDER_KEY"
    assert "openai/gpt-4o" in routed
    assert "qwen2.5:7b-instruct" in routed  # the local models stay: unsendable material runs there


def test_the_conduit_is_told_the_routes_and_codes_and_the_gateway_the_key_by_reference(
    tmp_path: Path,
) -> None:
    rendered = render(_config(tmp_path, WITH_PROVIDER), resolver=_fake_resolver)
    env = rendered.artefacts["deployment.env"]
    assert "OSPREY_PROVIDER_EXTRACTION_MODEL=openai/gpt-4o-mini" in env
    assert "OSPREY_PROVIDER_VISION_MODEL=openai/gpt-4o" in env
    assert "OSPREY_SENDABLE_HANDLING_CODES=P" in env
    compose = yaml.safe_load(rendered.artefacts["compose.yaml"])
    gateway = compose["services"]["litellm"]["environment"]
    assert gateway["OSPREY_MODEL_PROVIDER_KEY"].startswith("${OSPREY_MODEL_PROVIDER_KEY:?")
    assert "OSPREY_MODEL_PROVIDER_KEY" not in compose["services"]["api"].get("environment", {})


def test_no_generated_file_ever_holds_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OSPREY_MODEL_PROVIDER_KEY", KEY)
    config = _config(tmp_path, WITH_PROVIDER)
    rendered = render(config, resolver=_fake_resolver)
    for name, text in {**rendered.artefacts, "litellm.yaml": render_litellm_config(config)}.items():
        assert KEY not in text, name


def test_apply_writes_the_key_only_from_the_environment_and_refuses_without_it(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, WITH_PROVIDER)
    assert provider_secret_lines(config, {"OSPREY_MODEL_PROVIDER_KEY": KEY}) == (
        f"OSPREY_MODEL_PROVIDER_KEY={KEY}\n"
    )
    with pytest.raises(ApplyFailed, match="OSPREY_MODEL_PROVIDER_KEY"):
        provider_secret_lines(config, {})
    local = _config(tmp_path, ModelsConfig())
    assert provider_secret_lines(local, {"OSPREY_MODEL_PROVIDER_KEY": KEY}) == ""


def test_a_local_only_deployment_renders_no_provider(tmp_path: Path) -> None:
    config = _config(tmp_path, ModelsConfig())
    rendered = render(config, resolver=_fake_resolver)
    assert "OSPREY_PROVIDER_" not in rendered.artefacts["deployment.env"]
    compose = yaml.safe_load(rendered.artefacts["compose.yaml"])
    assert "OSPREY_MODEL_PROVIDER_KEY" not in compose["services"]["litellm"]["environment"]
    assert "os.environ/" not in render_litellm_config(config)
